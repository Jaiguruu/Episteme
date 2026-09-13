using System;

namespace Example.Gen
{
    public interface IHandler4
    {
        bool Handle(string payload);
    }

    public class Base4
    {
        protected string Name;
    }

    public class Service4 : Base4, IHandler4
    {
        public Service4(string name)
        {
            this.Name = name;
        }

        public bool Handle(string payload)
        {
            this.Validate(payload);
            return true;
        }

        private void Validate(string payload) { }
    }
}
